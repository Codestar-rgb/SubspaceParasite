package com.srp.client.renderer;

import com.srp.client.model.InfVillagerModel;
import com.srp.entity.InfVillagerEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfVillagerRenderer extends GeoEntityRenderer<InfVillagerEntity> {

    public InfVillagerRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfVillagerModel());
    }
}
