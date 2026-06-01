package com.srp.client.renderer;

import com.srp.client.model.SpeVillagerModel;
import com.srp.entity.SpeVillagerEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class SpeVillagerRenderer extends GeoEntityRenderer<SpeVillagerEntity> {

    public SpeVillagerRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new SpeVillagerModel());
    }
}
