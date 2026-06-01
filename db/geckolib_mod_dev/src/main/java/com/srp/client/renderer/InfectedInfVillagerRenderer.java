package com.srp.client.renderer;

import com.srp.client.model.InfectedInfVillagerModel;
import com.srp.entity.InfectedInfVillagerEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfectedInfVillagerRenderer extends GeoEntityRenderer<InfectedInfVillagerEntity> {

    public InfectedInfVillagerRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfectedInfVillagerModel());
    }
}
